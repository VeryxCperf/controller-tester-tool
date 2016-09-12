With the help of the script "odl_tester_with_packet_capture_for_bulk_and_single_flow.py", we can calculate the "Proactive Flow Provisioing Time" in two scenario as following

i) Bulk flows install in single REST request message. For this test the CLI command should be as following,

Note: For bulk flows install in single REST request we should use the option --fpr=number_of_flows & --bulk_add=True

Ex:python odl_tester_with_packet_capture_for_bulk_and_single_flow.py --host=192.168.75.211 --port=8181 --flows=100 --timeout=10 --NBport=eth1 --SBport=eth2 --bulk_add=True --fpr=100

ii) Single flow install in single REST request message. For this test the CLI command should be as following,

Note: For single flow install in single REST request we should use the option --fpr=1 & --bulkAdd=False

Ex:python odl_tester_with_packet_capture_for_bulk_and_single_flow.py --host=192.168.75.211 --port=8181 --flows=100 --timeout=10 --NBport=eth1 --SBport=eth2 --bulk_add=False --fpr=1

For more help information about the script, execute the following CLI command,

python odl_tester_with_packet_capture_for_bulk_and_single_flow.py --help

