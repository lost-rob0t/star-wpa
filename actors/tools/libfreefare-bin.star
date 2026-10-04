(actor wpa-tool-libfreefare-bin
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-libfreefare-bin"
   :accepts ()
   :produces ()
   :handler wpa-tool-libfreefare-bin-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-libfreefare-bin") (package "libfreefare-bin") (family "nfc-rfid")
              (commandBoundary "operator-local-json-file"))))
