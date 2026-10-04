(actor wpa-tool-crackle
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-crackle"
   :accepts ()
   :produces ()
   :handler wpa-tool-crackle-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-crackle") (package "crackle") (family "bluetooth")
              (commandBoundary "operator-local-json-file"))))
