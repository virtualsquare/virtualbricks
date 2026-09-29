# Certificates of the tests

Throwaway certificates for the tests of the ssl sockets, valid for 100
years: `server` for `localhost` and `127.0.0.1`, and two clients, `alice`
and `bob`. They were made with the commands of `virtualbricks(1)`:

```
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 \
    -nodes -days 36500 -subj /CN=localhost \
    -addext subjectAltName=DNS:localhost,IP:127.0.0.1 \
    -keyout server.key -out server.pem
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 \
    -nodes -days 36500 -subj /CN=alice -keyout alice.key -out alice.pem
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 \
    -nodes -days 36500 -subj /CN=bob -keyout bob.key -out bob.pem
```

Their keys are public: never use them for anything else.
