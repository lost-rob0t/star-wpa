(actor wpa-aircrack
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-aircrack"
   :accepts ()
   :produces ()
   :handler wpa-aircrack-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "aircrack") (commandBoundary "operator-local-json-file"))))
