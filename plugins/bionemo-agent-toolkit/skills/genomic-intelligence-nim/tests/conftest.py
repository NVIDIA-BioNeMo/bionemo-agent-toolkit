def pytest_configure(config):
    config.addinivalue_line("markers", "integration: live-API test; requires GI_API_KEY")
