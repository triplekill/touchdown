# Copyright 2014 Isotoma Limited
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

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import asymmetric, serialization
from cryptography.x509 import load_pem_x509_certificate

from touchdown.core import argument, datetime, errors
from touchdown.core.plan import Plan
from touchdown.core.resource import Resource

from ..account import BaseAccount
from ..replacement import (
    ReplacementApply,
    ReplacementDescribe,
    ReplacementDestroy,
)


def split_cert_chain(chain):
    lines = []
    for line in chain.split("\n"):
        if not line:
            continue
        lines.append(line)
        if line == "-----END CERTIFICATE-----":
            yield "\n".join(lines).encode("utf-8")
            lines = []
    if lines:
        yield "\n".join(lines).encode("utf-8")


class ServerCertificate(Resource):

    resource_name = "server_certificate"
    field_order = [
        "private_key",
        "certificate_body",
        "certificate_chain",
    ]

    name = argument.String(field="ServerCertificateName", update=False)
    path = argument.String(field='Path')
    private_key = argument.String(field="PrivateKey", secret=True, update=False)
    certificate_body = argument.String(field="CertificateBody")
    certificate_chain = argument.String(field="CertificateChain")

    account = argument.Resource(BaseAccount)

    def clean_certificate_body(self, value):
        backend = default_backend()
        cert = load_pem_x509_certificate(value, backend)
        private_key = serialization.load_pem_private_key(
            self.private_key.encode("utf-8"),
            password=None,
            backend=backend,
        )

        if cert.public_key().public_numbers() != private_key.public_key().public_numbers():
            raise errors.Error(
                "Certificate does not match private_key",
            )

        return value.strip()

    def clean_certificate_chain(self, value):
        # Perform a basic validation of the SSL chain.
        # This isn't a complete and secure validation. It's just to try and
        # catch problems before doing a deployment.
        backend = default_backend()

        certs = [load_pem_x509_certificate(self.certificate_body, backend)]
        for cert in split_cert_chain(value):
            certs.append(load_pem_x509_certificate(cert, backend))

        for i, (cert, issuer) in enumerate(zip(certs, certs[1:])):
            verifier = issuer.public_key().verifier(
                cert.signature,
                asymmetric.padding.PKCS1v15(),
                cert.signature_hash_algorithm,
            )
            verifier.update(cert.tbs_certificate_bytes)
            try:
                verifier.verify()
            except:
                raise errors.Error(
                    "Invalid chain: {} (issued by {}) -> {}. At position {}.".format(
                        cert.subject,
                        cert.issuer,
                        issuer.subject,
                        i
                    ))

        return value.strip()


class Describe(ReplacementDescribe, Plan):

    resource = ServerCertificate
    service_name = 'iam'
    describe_action = "list_server_certificates"
    describe_envelope = "ServerCertificateMetadataList"
    describe_filters = {}
    key = 'ServerCertificateName'
    biggest_serial = 0

    def get_possible_objects(self):
        for obj in super(Describe, self).get_possible_objects():
            response = self.client.get_server_certificate(
                ServerCertificateName=self.name_for_remote(obj),
            )['ServerCertificate']

            result = dict(response['ServerCertificateMetadata'])
            result['CertificateBody'] = response['CertificateBody']
            result['CertificateChain'] = response['CertificateChain']

            yield result


class Apply(ReplacementApply, Describe):

    create_action = "upload_server_certificate"
    create_response = "not-that-useful"
    destroy_action = "delete_server_certificate"

    def is_stale(self, server_certificate):
        if server_certificate['Expiration'] >= datetime.now():
            # Don't delete valid certificates
            return False
        return super(Apply, self).is_stale(server_certificate)


class Destroy(ReplacementDestroy, Describe):

    destroy_action = "delete_server_certificate"
