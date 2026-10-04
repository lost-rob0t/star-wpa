(actor wpa-tool-mfterm
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-mfterm"
   :accepts ()
   :produces ()
   :handler wpa-tool-mfterm-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-mfterm") (package "mfterm") (family "nfc-rfid")
              (commandBoundary "operator-local-json-file"))))
