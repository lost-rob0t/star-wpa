(actor wpa-tool-mfcuk
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-mfcuk"
   :accepts ()
   :produces ()
   :handler wpa-tool-mfcuk-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-mfcuk") (package "mfcuk") (family "nfc-rfid")
              (commandBoundary "operator-local-json-file"))))
