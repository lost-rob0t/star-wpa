(actor wpa-tool-yersinia
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-yersinia"
   :accepts ()
   :produces ()
   :handler wpa-tool-yersinia-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-yersinia") (package "yersinia") (family "network")
              (commandBoundary "operator-local-json-file"))))
