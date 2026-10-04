(actor wpa-listener
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-listener"
   :accepts ()
   :produces ()
   :handler wpa-listener-handler
   :restart permanent
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "listener") (commandBoundary "operator-local-json-file"))))
