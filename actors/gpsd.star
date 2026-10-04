(actor wpa-gpsd
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-gpsd"
   :accepts ()
   :produces ()
   :handler wpa-gpsd-handler
   :restart permanent
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "gpsd") (commandBoundary "operator-local-json-file"))))
