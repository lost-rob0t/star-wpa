(actor wpa-tool-bluez-hcidump
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-bluez-hcidump"
   :accepts ()
   :produces ()
   :handler wpa-tool-bluez-hcidump-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-bluez-hcidump") (package "bluez-hcidump") (family "bluetooth")
              (commandBoundary "operator-local-json-file"))))
