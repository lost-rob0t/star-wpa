(actor wpa-tool-mdk4
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-mdk4"
   :accepts ()
   :produces ()
   :handler wpa-tool-mdk4-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-mdk4") (package "mdk4") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
