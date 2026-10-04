(actor wpa-trilateration
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-trilateration"
   :accepts ()
   :produces ()
   :handler wpa-trilateration-handler
   :restart permanent
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "trilateration") (commandBoundary "operator-local-json-file"))))
