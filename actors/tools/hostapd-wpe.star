(actor wpa-tool-hostapd-wpe
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-hostapd-wpe"
   :accepts ()
   :produces ()
   :handler wpa-tool-hostapd-wpe-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-hostapd-wpe") (package "hostapd-wpe") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
