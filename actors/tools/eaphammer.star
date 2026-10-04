(actor wpa-tool-eaphammer
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-eaphammer"
   :accepts ()
   :produces ()
   :handler wpa-tool-eaphammer-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-eaphammer") (package "eaphammer") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
