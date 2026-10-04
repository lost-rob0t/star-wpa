# Wireless ownership migration

`star-wpa` owns wireless provider parsing, actor declarations, local effects and wireless query projections. StarLang owns the language/runtime and canonical document schema; StarIntel Server owns HTTP authentication, registry-based ingest, tenant authorization and general spatial indexing. StarIntel Edge owns host/device runtime mechanics.

The GitHub source inventory inspected on 2026-10-04: server default-branch commit `ce14c77ccd2f51f543410fdeef3d78fb9978b769`, and PR #311 head `8c74bf3e22146479814f1eb33582df7b2cf0c388`.

| Source | Extracted/replaced responsibility | Destination |
|---|---|---|
| `lost-rob0t/starintel-server`, open PR #311, `addons/wardrive/wardrive.lisp` | WarStar/WiGLE observation conversion | `star_wpa.ingest.ingest_wardrive`, `actors/wardrive.star` |
| server `source/views/networks.json` | Wireless network indexing | canonical `networks_by_bssid` and `networks_by_security` |
| server `source/views/devices.json` | Device indexing | canonical `stations_by_mac` and network records |
| server `source/views/observations.json` | Wireless sighting indexing | canonical event/receiver/transmitter/time views and multilateration windows |

This is a semantic extraction into generated 0.10.1 contracts, not copying the old schema. Legacy `wireless-emitter` and `wireless-sighting` top-level dtypes are not 0.10.1 output. Receiver geography becomes observation-linked `geo-point`/`location`; it does not become a direct AP location.

No implementations of aircrack, Kismet, GPSD or deauthentication actors were found on the current GitHub default branches of server, pro-actors or edge. Their actors in this package are new. The original source repository is still an unresolved user clarification, so no unidentified source code was deleted and no claim is made that every possible upstream actor has been found.

The server PR remains intact. Its authenticated HTTP route should consume this package's canonical output through the maintained registry/ingest contract once that server's schema lock is repinned and verified. The inspected server lock is still release 0.9.1/schema 0.9.0; this package does not bypass or pretend that gate is green. Removing the old converter/views or replacing the server's pending PR requires a coordinated upstream change. Old view clients must opt into the new design document and canonical shapes; no silent compatibility aliases are provided.

The main implementation is reviewable in this repository. Live radio, real GPS hardware, deployed Kismet and multi-tenant server integration are not established by fixture, local socket or disposable CouchDB tests.

Kismet field verification used the upstream `phy_80211_components.h`, `phy_80211_components.cc` and `devicetracker_component.cc` sources retrieved on 2026-10-04 from https://github.com/kismetwireless/kismet: `dot11.device.last_beaconed_ssid_record`, `dot11.advertisedssid.ssid`, `dot11.advertisedssid.crypt_string`, `dot11.device.last_bssid` and `kismet.device.base.crypt`. This confirms the adapter field names, not compatibility with every deployed Kismet version.
