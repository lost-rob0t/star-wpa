(actor wpa-tool-wpasupplicant
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-wpasupplicant"
   :accepts ()
   :produces ()
   :handler wpa-tool-wpasupplicant-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-wpasupplicant") (package "wpasupplicant") (family "wifi")
              (commandBoundary "operator-local-json-file"))))
