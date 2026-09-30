# -*- test-case-name: virtualbricks.tests.console.test_tls -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2019 Virtualbricks team

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""
The TLS of an ssl socket: the certificate of Virtualbricks, and the
certificates that its clients show. It is the only module of Virtualbricks
that needs pyOpenSSL, and it is imported only for an ssl socket, so that a
Virtualbricks without one runs without pyOpenSSL.

Twisted's own ``ssl:`` has no way to ask the clients for certificates:
``caCertsDir`` is a keyword of its clients only. So the options are built
here, with ``CertificateOptions(trustRoot=...)``.
"""

from __future__ import annotations

import os
import re

from OpenSSL import SSL, crypto
from twisted.internet import error, ssl

from virtualbricks.console import wire
from virtualbricks.i18n import _

CERTIFICATE = re.compile(
    rb"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", re.DOTALL
)


def _read(path):
    try:
        with open(path, "rb") as file:
            return file.read()
    except FileNotFoundError:
        raise wire.Unusable(
            _("{path} doesn't exist").format(path=path)
        ) from None
    except OSError as exc:
        raise wire.Unusable(f"{path}: {exc.strerror}") from None


def _certificate(path, data=None):
    try:
        return ssl.Certificate.loadPEM(_read(path) if data is None else data)
    except (crypto.Error, SSL.Error, ValueError):
        raise wire.Unusable(
            _("{path} isn't a certificate in PEM").format(path=path)
        ) from None


def private_certificate(cert_path, key_path):
    """
    The certificate of cert_path with the key of key_path, which can be the
    same file; raise wire.Unusable if they can't be read, or don't match.
    """

    certificate = _certificate(cert_path)
    try:
        key = ssl.KeyPair.load(_read(key_path), crypto.FILETYPE_PEM)
    except (crypto.Error, ValueError):
        raise wire.Unusable(
            _("{path} isn't a private key in PEM").format(path=key_path)
        ) from None
    try:
        return ssl.PrivateCertificate.fromCertificateAndKeyPair(
            certificate, key
        )
    except error.VerifyError:
        raise wire.Unusable(
            _("The key {key} isn't that of the certificate {cert}").format(
                key=key_path, cert=cert_path
            )
        ) from None


def chain(path):
    """The certificates of the file at path, between one and its CA."""

    found = CERTIFICATE.findall(_read(path))
    if not found:
        raise wire.Unusable(
            _("{path} has no certificate in PEM").format(path=path)
        )
    return [_certificate(path, data).original for data in found]


def trusted(folder):
    """
    The certificates of the .pem files of folder, as Twisted reads its
    caCertsDir; raise wire.Unusable if it has none.
    """

    try:
        names = sorted(os.listdir(folder))
    except FileNotFoundError:
        raise wire.Unusable(
            _("{path} doesn't exist").format(path=folder)
        ) from None
    except NotADirectoryError:
        raise wire.Unusable(
            _("{path} isn't a folder").format(path=folder)
        ) from None
    except OSError as exc:
        raise wire.Unusable(f"{folder}: {exc.strerror}") from None
    certificates = []
    for name in names:
        if not name.lower().endswith(".pem"):
            continue
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            certificates.append(_certificate(path))
    if not certificates:
        raise wire.Unusable(
            _("{path} has no .pem certificate").format(path=folder)
        )
    return certificates


def server_options(socket):
    """
    The TLS options of socket, a wire.Socket of type ssl: its certificate,
    and the certificates that its clients show when it has ca_dir. Raise
    wire.Unusable if one of its files can't be used.
    """

    certificate = private_certificate(
        socket.cert or socket.private_key, socket.private_key
    )
    extra = chain(socket.chain) if socket.chain else None
    trust = None
    if socket.ca_dir is not None:
        trust = ssl.trustRootFromCertificates(trusted(socket.ca_dir))
    return ssl.CertificateOptions(
        privateKey=certificate.privateKey.original,
        certificate=certificate.original,
        extraCertChain=extra,
        trustRoot=trust,
    )


def client_options(socket):
    """
    The TLS options of the windows for socket, a wire.Socket of --connect
    of type ssl: the certificates they trust for Virtualbricks, those of
    ca_dir or else of the system, and their own certificate, if any. Raise
    wire.Unusable if one of its files can't be used.
    """

    if socket.ca_dir is not None:
        trust = ssl.trustRootFromCertificates(trusted(socket.ca_dir))
    else:
        trust = ssl.platformTrust()
    mine = None
    if socket.private_key or socket.cert:
        mine = private_certificate(
            socket.cert or socket.private_key,
            socket.private_key or socket.cert,
        )
    return ssl.optionsForClientTLS(
        socket.host, trustRoot=trust, clientCertificate=mine
    )


def common_name(certificate):
    """The name of a client's certificate, a pyOpenSSL X509, for the log."""

    if certificate is None:
        return None
    return certificate.get_subject().commonName


def describe(failure):
    """Why a TLS handshake failed, from the Failure of the connection."""

    exc = failure.value
    if isinstance(exc, SSL.Error) and exc.args and exc.args[0]:
        reasons = [item[-1] for item in exc.args[0] if item]
        if all(isinstance(reason, str) for reason in reasons):
            return "; ".join(reasons)
    return failure.getErrorMessage()
