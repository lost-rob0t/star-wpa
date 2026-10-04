(actor wpa-deauth
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-deauth"
   :accepts ()
   :produces ()
   :handler wpa-deauth-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "deauth") (commandBoundary "operator-local-json-file"))))
