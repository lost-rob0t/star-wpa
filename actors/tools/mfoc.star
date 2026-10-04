(actor wpa-tool-mfoc
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-mfoc"
   :accepts ()
   :produces ()
   :handler wpa-tool-mfoc-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-mfoc") (package "mfoc") (family "nfc-rfid")
              (commandBoundary "operator-local-json-file"))))
