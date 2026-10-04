(actor wpa-tool-bully
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-bully"
   :accepts ()
   :produces ()
   :handler wpa-tool-bully-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-bully") (package "bully") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
