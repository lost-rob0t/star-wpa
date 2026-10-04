(actor wpa-tool-gpsd
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-gpsd"
   :accepts ()
   :produces ()
   :handler wpa-tool-gpsd-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-gpsd") (package "gpsd") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
