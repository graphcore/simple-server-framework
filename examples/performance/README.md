# Performance testing tools
The tools provided in this directory support basic load testing of a running application server. The scripts are designed as input to the [Locust](https://github.com/locustio/locust) performance testing tool.

# Prerequisites
Install all required packages:
```bash
$ pip install -r requirements.txt
```

# Configuration
To test your application, modify/add the requests in the `locust_ssf_simple_test.py` file to match your specific application. The utility function `testSSF` will create test clients for SSF supported APIs so there is no need to create separate Locust files for different APIs. gRPC tests are performed based on HTTP tests by using the `GRPCSession` proxy session class which translates HTTP requests to gRPC requests.

The default implementation tests the simple application example from `examples/simple`.
A full guide on how to write the tests can be found on [Locust documentation page](https://docs.locust.io/).

# Usage
1. Start your application server using SSF.
2. Run the Locust script. By default the script is configured to connect to the server on address `127.0.0.1:8100`. If you want a different address, this can be configured on the command line. Adding the `--class-picker` parameter allows you to choose an API from the Locust web UI rather than having to write separate test files for all SSF supported APIs. Example command line given below:

```bash
$ locust -f locust_ssf_simple_test.py -H http://customIp.com:8000 --class-picker
```

3. The Locust Web UI is exposed on port 8089 and will allow you to choose one of SSF supported APIs (make sure only one test class is selected), start the test and adjust test parameters.