(actor wpa-tool-rtl-433
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-rtl-433"
   :accepts ()
   :produces ()
   :handler wpa-tool-rtl-433-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-rtl-433") (package "rtl-433") (family "sdr")
              (commandBoundary "operator-local-json-file"))))
