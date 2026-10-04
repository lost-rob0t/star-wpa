(actor wpa-tool-mdk3
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-mdk3"
   :accepts ()
   :produces ()
   :handler wpa-tool-mdk3-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-mdk3") (package "mdk3") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
