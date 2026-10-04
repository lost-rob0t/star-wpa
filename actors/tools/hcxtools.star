(actor wpa-tool-hcxtools
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-hcxtools"
   :accepts ()
   :produces ()
   :handler wpa-tool-hcxtools-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-hcxtools") (package "hcxtools") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
