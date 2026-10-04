(actor wpa-tool-btscanner
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-btscanner"
   :accepts ()
   :produces ()
   :handler wpa-tool-btscanner-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-btscanner") (package "btscanner") (family "bluetooth")
              (commandBoundary "operator-local-json-file"))))
