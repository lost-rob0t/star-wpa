(actor wpa-tool-rtl-sdr
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-rtl-sdr"
   :accepts ()
   :produces ()
   :handler wpa-tool-rtl-sdr-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-rtl-sdr") (package "rtl-sdr") (family "sdr")
              (commandBoundary "operator-local-json-file"))))
