(actor wpa-tool-hcxdumptool
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-hcxdumptool"
   :accepts ()
   :produces ()
   :handler wpa-tool-hcxdumptool-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-hcxdumptool") (package "hcxdumptool") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
