(actor wpa-wardrive
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-wardrive"
   :accepts ()
   :produces ()
   :handler wpa-wardrive-handler
   :restart permanent
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "wardrive") (commandBoundary "operator-local-json-file"))))
