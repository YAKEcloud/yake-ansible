.PHONY: sync-charts

sync-charts:
	git clone --depth 1 --branch main https://github.com/vexxhost/chart-vendor.git .chart-vendor
	cd .chart-vendor && go build -o ../chart-vendor .
	./chart-vendor
	rm -rf chart-vendor .chart-vendor

sync-manifests:
	pipenv run gilt overlay
