(actor wpa-tool-wifi-honey
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-wifi-honey"
   :accepts ()
   :produces ()
   :handler wpa-tool-wifi-honey-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-wifi-honey") (package "wifi-honey") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
