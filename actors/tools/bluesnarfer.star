(actor wpa-tool-bluesnarfer
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-bluesnarfer"
   :accepts ()
   :produces ()
   :handler wpa-tool-bluesnarfer-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-bluesnarfer") (package "bluesnarfer") (family "bluetooth")
              (commandBoundary "operator-local-json-file"))))
