(actor wpa-tool-asleap
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-asleap"
   :accepts ()
   :produces ()
   :handler wpa-tool-asleap-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-asleap") (package "asleap") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
