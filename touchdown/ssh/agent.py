import struct
import os
from six.moves import socketserver
import threading

from paramiko.message import Message
from paramiko.common import asbytes
from paramiko.py3compat import byte_chr


if not hasattr(socketserver, "UnixStreamServer"):
    raise ImportError(__name__)


SSH_AGENT_FAILURE = 5
SSH_AGENT_SUCCESS = 6
SSH2_AGENT_IDENTITIES_ANSWER = 12
SSH2_AGENT_SIGN_RESPONSE = 14


class ConnectionError(Exception):
    pass


class AgentRequestHandler(socketserver.BaseRequestHandler):

    def _read(self, wanted):
        result = ''
        while len(result) < wanted:
            buf = self.request.recv(wanted - len(result))
            if not buf:
                raise ConnectionError()
            result += buf
        return result

    def read_message(self):
        size = struct.unpack('>I', self._read(4))[0]
        msg = Message(self._read(size))
        return ord(msg.get_byte()), msg

    def send_message(self, msg):
        msg = asbytes(msg)
        self.request.sendall(struct.pack('>I', len(msg)) + msg)

    def handler_11(self, msg):
        # SSH2_AGENTC_REQUEST_IDENTITIES = 11
        m = Message()
        m.add_byte(byte_chr(SSH2_AGENT_IDENTITIES_ANSWER))
        m.add_int(len(self.server.identities))
        for pkey, comment in self.server.identities.values():
            m.add_string(pkey.asbytes())
            m.add_string(comment)
        return m

    def handler_13(self, msg):
        # SSH2_AGENTC_SIGN_REQUEST = 13
        pkey, comment = self.server.identities.get(msg.get_binary(), (None, None))
        data = msg.get_binary()
        msg.get_int()
        m = Message()
        if not pkey:
            m.add_byte(chr(SSH_AGENT_FAILURE))
            return m
        m.add_byte(chr(SSH2_AGENT_SIGN_RESPONSE))
        m.add_string(pkey.sign_ssh_data(data).asbytes())
        return m

    def handle(self):
        while True:
            try:
                mtype, msg = self.read_message()
            except ConnectionError:
                return

            handler = getattr(self, "handler_{}".format(mtype))
            if not handler:
                continue

            self.send_message(handler(msg))


class AgentServer(socketserver.UnixStreamServer):

    def __init__(self, socket_file):
        socketserver.UnixStreamServer.__init__(self, socket_file, AgentRequestHandler)
        self.identities = {}

    def add(self, pkey, comment):
        self.identities[pkey.asbytes()] = (pkey, comment)

    def serve_while_pid(self, pid):
        t = threading.Thread(target=self.serve_forever)
        t.daemon = True
        t.start()

        while os.waitpid(pid, 0)[0] != pid:
            pass

        self.shutdown()
        self.server_close()
