(actor wpa-tool-blueranger
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-blueranger"
   :accepts ()
   :produces ()
   :handler wpa-tool-blueranger-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-blueranger") (package "blueranger") (family "bluetooth")
              (commandBoundary "operator-local-json-file"))))
