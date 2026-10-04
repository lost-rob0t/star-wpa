(actor wpa-kismet
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-kismet"
   :accepts ()
   :produces ()
   :handler wpa-kismet-handler
   :restart permanent
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "kismet") (commandBoundary "operator-local-json-file"))))
