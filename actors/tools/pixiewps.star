(actor wpa-tool-pixiewps
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-pixiewps"
   :accepts ()
   :produces ()
   :handler wpa-tool-pixiewps-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-pixiewps") (package "pixiewps") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
