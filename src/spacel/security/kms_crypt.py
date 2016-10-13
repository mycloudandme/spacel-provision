import logging

from botocore.exceptions import ClientError
from Crypto import Random
from Crypto.Cipher import AES
from Crypto.Util.py3compat import bchr, bord

import six
from spacel.security.payload import EncryptedPayload

logger = logging.getLogger('spacel.security.kms_crypt')

BLOCK_SIZE = AES.block_size
CIPHER_MODE = AES.MODE_CBC


class KmsCrypto(object):
    """
    Uses KMS to encrypt/decrypt data with AES-256.
    """

    def __init__(self, clients, kms_key):
        self._kms_key = kms_key
        self._clients = clients
        self._random = Random.new()

    def encrypt(self, app, region, plaintext):
        """
        Encrypt data for an application.
        :param app:  Space app.
        :param region:  Region.
        :param plaintext: Plaintext blob.
        :return: EncryptedPayload.
        """
        # Get DEK:
        logger.debug('Fetching fresh data key...')
        try:
            alias_name = self._kms_key.get_key_alias(app)
            kms = self._clients.kms(region)
            data_key = kms.generate_data_key(KeyId=alias_name,
                                             KeySpec='AES_256')
        except ClientError as e:
            e_message = e.response['Error'].get('Message', '')
            if 'is not found' in e_message:
                # Key not found, create and try again:
                self._kms_key.create_key(app, region)
                return self.encrypt(app, region, plaintext)

        # Encode and pad data:
        encoding = 'bytes'
        if isinstance(plaintext, six.string_types):
            encoding = 'utf-8'
            if six.PY3:  # pragma: no cover
                plaintext = bytes(plaintext, encoding)
            else:  # pragma: no cover
                plaintext = plaintext.encode(encoding)
        pad_length = BLOCK_SIZE - (len(plaintext) % BLOCK_SIZE)
        padded = plaintext + (pad_length * bchr(pad_length))
        logger.debug('Padded %s %s to %s.', len(plaintext), encoding,
                     len(padded))

        logger.debug('Encrypting data with data key...')
        iv = self._random.read(BLOCK_SIZE)

        cipher = AES.new(data_key['Plaintext'], CIPHER_MODE, iv)
        ciphertext = cipher.encrypt(padded)

        encrypted_key = data_key['CiphertextBlob']
        return EncryptedPayload(iv, ciphertext, encrypted_key, region, encoding)

    def decrypt_payload(self, payload):
        """
        Decrypt an encrypted payload.
        :param payload: EncryptedPayload.
        :return: Decrypted payload.
        """
        return self.decrypt(payload.iv, payload.ciphertext, payload.key,
                            payload.key_region, payload.encoding)

    def decrypt(self, iv, ciphertext, key, key_region, encoding):
        """
        Decrypt.
        :param iv: Encryption IV.
        :param ciphertext:  Ciphertext.
        :param key: Encrypted data key.
        :param key_region: Data key region (KMS).
        :param encoding:  Encoding
        :return: Decrypted payload.
        """
        # Decrypt DEK:
        logger.debug('Decrypting data key...')
        kms = self._clients.kms(key_region)
        decrypted_key = kms.decrypt(CiphertextBlob=key)

        # Decrypt data:
        cipher = AES.new(decrypted_key['Plaintext'], CIPHER_MODE, iv)
        plaintext = cipher.decrypt(ciphertext)

        # Remove pad:
        pad_length = bord(plaintext[-1])
        actual_pad = plaintext[-pad_length:]
        expected_pad = bchr(pad_length) * pad_length
        if actual_pad != expected_pad:
            raise ValueError('Incorrect padding')
        unpadded = plaintext[:-pad_length]

        if encoding == 'bytes':  # pragma: no cover
            return unpadded
        if six.PY3:  # pragma: no cover
            return str(unpadded, encoding)
        else:  # pragma: no cover
            return unpadded.decode(encoding)
