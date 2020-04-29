"""This Module handles the identitydb object"""
import os
import tempfile
from threading import Thread
from pem import parse_file
import libpkpass.crypto as crypto
from libpkpass.errors import FileOpenError, CliArgumentError

    ##########################################################################
class IdentityDB():
    """ User database class.  Contains information about the identities of and
        things pertinent to recipients and their groups and keys.              """
    ##########################################################################

    def __init__(self):
        self.extensions = {'certificate': ['.cert', '.crt'],
                           'key': '.key'}
        self.cabundle = ""
        self.iddb = {}

    def __repr__(self):
        return "%s(%r)" % (self.__class__, self.__dict__)

    def __str__(self):
        return "%r" % self.__dict__

    def _load_certs_from_external(self, connection_map, nocache):
        if 'base_directory' in connection_map and connection_map['base_directory']:
            temp_dir = connection_map['base_directory']
            del connection_map['base_directory']
        else:
            temp_dir = str(tempfile.gettempdir())

        for key, value in connection_map.items():
            dirname = os.path.join(temp_dir, str(key))
            if not os.path.exists(dirname):
                os.makedirs(dirname)
            if nocache or not os.listdir(dirname):
                encoded = key
                connector = encoded.lower()
                connector = __import__(connector, fromlist=[encoded])
                connector = getattr(connector, encoded)
                connector = connector(value)
                certs = connector.list_certificates()
                for name, certlist in certs.items():
                    with open(os.path.join(dirname, str(name)) +  str(self.extensions['certificate'][0]), 'w') as tmpcert:
                        tmpcert.write("\n".join(certlist))

            self._load_from_directory(dirname, 'certificate')

        #######################################################################
    def _load_from_directory(self, path, filetype):
        """ Helper function to read in (keys|certs) and store them correctly """
        #######################################################################
        try:
            for fname in os.listdir(path):
                if fname.endswith(tuple(self.extensions[filetype])):
                    uid = fname.split('.')[0]
                    filepath = os.path.join(path, fname)
                    try:
                        self.iddb[uid]["%s_path" % filetype] = filepath
                    except KeyError as error:
                        identity = {'uid': fname.split('.')[0],
                                    "%s_path" % filetype: filepath}
                        self.iddb[identity['uid']] = identity
        except OSError as error:
            raise FileOpenError(path, str(error.strerror))

        #######################################################################
    def load_certs_from_directory(self,
                                  certpath,
                                  verify_on_load=False,
                                  connectmap=None,
                                  nocache=False):
        """ Read in all x509 certificates from directory and name them as found """
        #######################################################################
        if connectmap:
            self._load_certs_from_external(connectmap, nocache)
        if certpath:
            self._load_from_directory(certpath, 'certificate')
        if verify_on_load:
            threads = []
            for identity, _ in self.iddb.items():
                threads.append(Thread(target=self.verify_identity,
                                      args=(identity, [])))
                threads[-1].start()
            for thread in threads:
                thread.join()

        #######################################################################
    def verify_identity(self, identity, results):
        """ Read in all rsa keys from directory and name them as found
        results is a meaningless parameter, but is required to make threading work
        """
        #######################################################################
        try:
            self.iddb[identity]['cabundle'] = self.cabundle
            self.iddb[identity]['certs'] = []
            for cert in parse_file(self.iddb[identity]['certificate_path']):
                cert = cert.as_bytes()
                cert_dict = {}
                cert_dict['cert_bytes'] = cert
                cert_dict['verified'] = crypto.pk_verify_chain(cert, self.iddb[identity]['cabundle'])
                cert_dict['fingerprint'] = crypto.get_cert_fingerprint(cert)
                cert_dict['subject'] = crypto.get_cert_subject(cert)
                cert_dict['issuer'] = crypto.get_cert_issuer(cert)
                cert_dict['enddate'] = crypto.get_cert_enddate(cert)
                cert_dict['issuerhash'] = crypto.get_cert_issuerhash(cert)
                cert_dict['subjecthash'] = crypto.get_cert_subjecthash(cert)
                self.iddb[identity]['certs'].append(cert_dict)
        except KeyError:
            raise CliArgumentError(
                "Error: Recipient '%s' is not in the recipient database" % identity)

        #######################################################################
    def load_keys_from_directory(self, path):
        """ Read in all rsa keys from directory and name them as found """
        #######################################################################
        if os.path.isdir(path):
            self._load_from_directory(path, 'key')
        # We used to print a warning on else here, but it seems unnecessary;
        # if a user is using PIVs/Smartcards, this warning could just annoy
        # them needlessly
