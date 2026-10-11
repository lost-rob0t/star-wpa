# Kismet collection deployment

## Where policy comes from

`star_wpa/__main__.py` loads the JSON file named by `STAR_WPA_POLICY_FILE`
before dispatching a request. An unset variable means no local policy. A named
file that cannot be read or parsed fails the invocation; there is no fallback.
`lisp/actors.lisp` runs `python -m star_wpa` through the process port, inheriting
the actor host's environment. Set these variables on the actual service or
launcher, not just an interactive shell. The Nix application wrappers do not
provide a policy, token or Kismet endpoint.

`kismetTokenUrls` must be a JSON array of complete, final destination URLs.
The request's `url` must match one entry exactly when a nonempty
`STAR_WPA_KISMET_TOKEN` is present. Scheme, hostname spelling, explicit port,
path, trailing slash and query string all matter. An origin or wildcard does
not authorize its children. Both same-origin and cross-origin redirects fail,
even when the redirect destination is also allowlisted.

Only `STAR_WPA_KISMET_TOKEN` supplies the token. Incoming `policy`,
`kismetTokenUrls` or `kismetTokenAuth` fields have no authority. A `tokenEnv`
other than `STAR_WPA_KISMET_TOKEN` is rejected, even when no token is set.
Without a token, collection sends no credentials and does not require this
credential destination allowlist. This setting is not a general network ACL.

## Authentication and endpoint format

Local policy chooses `kismetTokenAuth`:

| Value | Outgoing credential | Intended endpoint |
| --- | --- | --- |
| `bearer` (default) | Authorization Bearer header | Existing gateways that accept Bearer tokens |
| `cookie` | Cookie with the `KISMET` name | Direct Kismet API token authentication |

Unknown modes fail before transport when a token is present. Cookie tokens
must contain only valid RFC 6265 cookie value bytes; separators, whitespace,
control bytes and non-ASCII characters fail before transport. Requests cannot
choose this mode. No token is added to the URL, request JSON or emitted documents.

Kismet's [login documentation](https://www.kismetwireless.net/docs/api/login/)
specifies a `KISMET` cookie or URI parameter for API tokens. Use cookie mode
for direct Kismet; Bearer behavior is retained for existing gateways. A fixture
that accepts Bearer headers alone does not establish native Kismet compatibility.
Use a token with the `readonly` role for a read-only device endpoint.

The adapter issues GET and expects a JSON array of dotted-field device objects,
limited to 8 MiB and 1,000 devices. A datatables response object, NDJSON/ekjson,
login HTML or a redirect is not that contract. The example uses the documented
[recently active devices endpoint](https://www.kismetwireless.net/docs/api/devices/),
`/devices/last-time/-60/devices.json`, which supports GET. This is an example,
not an observation of the deployed endpoint. Choose the deployed final URL
and confirm its format and batch size. Native pagination is not implemented;
narrow the device window or expose an operator-controlled bounded array export
if a deployment exceeds the limit.

## Token-free configuration example

[examples/kismet-policy.json](../examples/kismet-policy.json) and
[examples/kismet-collect.json](../examples/kismet-collect.json) use a hypothetical
loopback Kismet service on port 2501, direct cookie authentication and matching
destination URLs. Replace that URL in both local files with the actual final
endpoint. Use HTTPS for a remote endpoint. Merge the two Kismet policy keys
into any existing operator policy; preserve its other settings.

An example installation of the policy (no secret contents):

```bash
install -d -m 700 "$HOME/.config/star-wpa"
install -m 600 examples/kismet-policy.json "$HOME/.config/star-wpa/policy.json"
install -m 600 examples/kismet-collect.json "$HOME/.config/star-wpa/kismet-collect.json"
export STAR_WPA_POLICY_FILE="$HOME/.config/star-wpa/policy.json"
```

After editing those local files, have the operator's keyring/auth-source or
secret provider inject `STAR_WPA_KISMET_TOKEN` into the collector environment.
Do not paste its value into shell commands, Nix expressions, tracked dotenv
files, request files or policy JSON. A service may use a launch-time credential
provider; its Nix expression should contain only nonsecret paths and settings.
The actor host and its adapter child must receive the same policy path and
token environment. Ensure the service user can read the selected policy.

## Verify a deployment without printing credentials

1. Locate the actual launch unit, script or actor host and resolve the policy
   path **in that process's environment**. Inspect only variable names and
   nonsecret paths. Avoid `env`, `set`, raw `/proc/.../environ`, HTTP debug dumps
   or unfiltered service properties, which can print tokens.
2. Identify its request file and final Kismet device-array URL. Check that
   no embedded credentials, token query parameters or fragment are present.
   Add the exact URL to the deployment-local `kismetTokenUrls` array while
   preserving other policy entries. Set cookie mode for direct Kismet.
3. Execute as the collector user with the same launcher/secret environment:

   ```bash
   umask 077
   python3 -m star_wpa kismet --request /operator/local/kismet-collect.json > /operator/local/kismet-documents.json
   ```

4. Check exit status and validate the resulting bundle locally using
   `star_wpa.contracts.validate_bundle`. Report only counts, document types,
   schema version and whether the expected source/time window was present.
   Keep device data private. The CLI reports only exception class names on
   failure, so correlate authentication/format problems with local Kismet
   logs without exposing token headers or payloads.
5. A successful empty array establishes a completed API request, not observed
   radio activity. Only a tested deployed path with expected observations
   supports a claim that live collection works.

## Validation evidence and limits

Run the maintained integration coverage with:

```bash
python3 -m unittest discover -s tests -p 'test_kismet_collection.py' -v
python3 -m unittest discover -s tests -p 'test_*.py' -v
nix flake check -L
```

The integration tests execute the actual adapter CLI with temporary local
policy/request files and synthetic tokens against two loopback HTTP servers.
They verify canonical 0.10.1 documents, example configuration, both auth modes,
missing/malformed policy, exact URL mismatches, unauthorized environment secret
selection, request policy injection, invalid cookie tokens, and 301/302/303/307/308
redirect rejection with no request reaching the redirect destination.
They are discovered by both the host suite and Nix adapter check.

Inspection on 2026-10-09 used Star-WPA main
`78696e2a05a950791345df697810b42e39a91e50` and dotfiles master
`76d0b59198c2a952b9af2cdaf1aa2d7e7c99d4d7`. The dotfiles checkout had no
Kismet/Star-WPA configuration matches. This workspace had no collector policy,
token environment or SSH configuration. Therefore no deployed policy was
edited, no real Kismet process was tested, and the actual deployed endpoint,
policy path and service remain unverified. Official API documentation was
retrieved on 2026-10-09; the deployed Kismet version still needs checking.


## Mocked CI versus deployed acceptance

Development does **not** wait for RF hardware or a reachable deployment. The
mocked lane runs the same maintained adapter and the same live-proof wrapper
against a local HTTP fixture with a synthetic token:

```bash
python3 -m unittest tests.test_live_kismet_proof -v
python3 -m unittest discover -s tests -p 'test_kismet_collection.py' -v
```

That lane is expected to run in CI. It proves request/policy handling,
credential destination controls, HTTP behavior, canonical StarIntel 0.10.1
validation, and sanitized reporting. It does not prove physical RF reception or
a particular deployed Kismet instance.

The deployed lane is intentionally separate and opt-in:

```bash
export STAR_WPA_POLICY_FILE=/operator/local/star-wpa-policy.json
# Inject STAR_WPA_KISMET_TOKEN through the deployment secret mechanism.
python3 scripts/live-kismet-proof.py \
  --request /operator/local/kismet-collect.json
```

The script prints only document counts, dtypes, dataset names and schema
versions. To retain the canonical document batch for a subsequent operator
controlled CouchDB test, request a new private file explicitly:

```bash
python3 scripts/live-kismet-proof.py \
  --request /operator/local/kismet-collect.json \
  --documents-out /operator/local/kismet-documents.json
```

The output file is created with mode 0600 and is never overwritten. A successful
empty response proves API connectivity only. Hardware/RF acceptance requires an
expected observation from the deployed collector and must be reported
separately from the mocked CI result.
