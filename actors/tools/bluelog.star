(actor wpa-tool-bluelog
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-bluelog"
   :accepts ()
   :produces ()
   :handler wpa-tool-bluelog-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-bluelog") (package "bluelog") (family "bluetooth")
              (commandBoundary "operator-local-json-file"))))
