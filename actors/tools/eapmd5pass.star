(actor wpa-tool-eapmd5pass
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-eapmd5pass"
   :accepts ()
   :produces ()
   :handler wpa-tool-eapmd5pass-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-eapmd5pass") (package "eapmd5pass") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
