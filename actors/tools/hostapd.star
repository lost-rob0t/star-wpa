(actor wpa-tool-hostapd
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-hostapd"
   :accepts ()
   :produces ()
   :handler wpa-tool-hostapd-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-hostapd") (package "hostapd") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
