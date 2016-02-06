# Copyright 2016 Isotoma Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import acme.challenges
import acme.client
import acme.jose

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtensionOID

import OpenSSL.crypto

from touchdown.core import argument, errors, resource
from touchdown.core.plan import Plan
from touchdown.interfaces import File, FileNotFound


class CertificateRequest(resource.Resource):

    resource_name = "acme_certificate_request"

    name = argument.String()
    domains = argument.String()

    private_key = argument.Resource(File)
    certificate_body = argument.Resource(File)
    certificate_chain = argument.Resource(File)

    validator = argument.Resource(resource.Resource)

    endpoint = argument.String(default="https://acme-v01.api.letsencrypt.org/directory")
    expiration_threshold = argument.Integer(default=45)


class Apply(Plan):

    _acme = None

    @property
    def acme(self):
        if not self._acme:
            # FIXME: Where to get acme key
            self._acme = acme.client.Client(
                self.resource.endpoint,
                key=acme.jose.JWKRSA(key=serialization.load_pem_private_key(
                    key,
                    password=None,
                    backend=default_backend(),
                ))
            )
        return self._acme

    def get_private_key(self):
        fp = self.get_service("fileio", self.resource.private_key).read()
        return serialization.load_pem_private_key(
            fp.read(),
            default_backend(),
        )

    def generate_csr(self):
        builder = x509.CertificateSigningRequestBuilder()
        builder = builder.subject_name(x509.Name([
            x509.NameAttribute(x509.NameOID.COMMON_NAME, self.resource.domains[0]),
        ]))
        builder = builder.add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName(domain) for domain in self.resource.domains]
            ),
            critical=False,
        )
        csr = builder.sign(self.get_private_key(), hashes.SHA256(), default_backend())
        return csr.public_bytes(serialization.Encoding.DER)

    def request_challenge(self, domain):
        return self.acme.request_domain_challenges(
            domain,
            new_authz_uri=self.acme.directory.new_authz,
        )

    def validate_challenges(self, challenges, domain):
        validator = self.get_service("acme:challenge", self.resource.validator)
        for combo in challenges.body.resolved_combinations:
            if combo[0].chall.typ == validator.challenge:
                return combo[0], validator.handle_challenge(self.acme, combo[0], domain)

        raise errors.Error("{} unable to handle any of the challenge: {}".format(
            self.resource.validator,
            ", ".join(a.typ for a in self.object["Challenges"][domain])
        ))

    def answer_challenge(self, challenge, domain):
        response = challenge.response(self.acme.key)

        verified = response.simple_verify(
            challenge.chall,
            domain,
            self.acme.key.public_key(),
        )

        if not verified:
            raise errors.Error("Failed verification")

        return self.acme.answer_challenge(
            challenge,
            response,
        )

    def _get_certificate(self, issuance):
        return OpenSSL.crypto.dump_certificate(
            OpenSSL.crypto.FILETYPE_PEM,
            issuance.body,
        )

    def _get_certificate_chain(self, issuance):
        return "\n".join([
            OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, cert)
            for cert in self.acme.fetch_chain(issuance)
        ])

    def do_domain_authorizations(self):
        for domain in self.resource.domains:
            authz = self.request_challenge(domain)
            challenge, result = self.validate_challenges(authz)
            self.answer_challenges(challenge, domain)
            # validator.cleanup_challenger(domain)
            yield authz

    def _request_certificate(self):
        issuance, _ = self.acme.poll_and_request_issuance(
            acme.jose.util.ComparableX509(
                OpenSSL.crypto.load_certificate_request(
                    OpenSSL.crypto.FILETYPE_ASN1,
                    self.generate_csr(),
                )
            ),
            authzrs=list(self.do_domain_authorizations()),
        )
        return self._get_certificate(issuance), self._get_certificate_chain(issuance)

    def is_certificate_stale(self, certificate):
        """
        Check if the certificate needs to be reissued
        """
        # FIXME: Can this function check to see if 'certificate' is revoked??
        if False:
            # "The first certificate nees to be issued"
            return True

        private_numbers = self.get_private_key().public_key().public_numbers()
        public_numbers = certificate.public_key().public_numbers()
        if private_numbers != public_numbers:
            # "The 'private_key' has changed so the certificate needs to be reissued"
            return True

        if certificate.subject not in self.domains:
            # "The subject of the certificate is not one of the requested 'domains'"
            return True

        ext = certificate.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        sans = ext.value.get_values_for_type(x509.DNSName)

        for san in sans:
            if san not in self.domains:
                # "The SAN '{}' is not one of the request 'domains'".format(san)
                return True

        for domain in self.domains:
            if domain not in sans:
                # "The domain '{}' has been added since the certificate was issued".format(domain)
                return True

        if False:
            # "The certificate will expire in X days; the renewal threshold is currently Y"
            return True

        return False

    def get_actions(self):
        return []
