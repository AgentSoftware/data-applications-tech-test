# The data

`persons-with-significant-control-snapshot-2026-10-29-sample.txt.gz` is a sample of the Persons with Significant Control (PSC) snapshot that Companies House published on 29 October 2026.

## Source

Companies House publishes the whole PSC register every week as one file on its [PSC data product page](https://download.companieshouse.gov.uk/en_pscdata.html). The full snapshot has about 16 million records, about 15 GB unzipped.

The fields are described in the [Companies House public data API specification](https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/resources/list?v=latest), under the persons-with-significant-control resources.

## Format

JSON lines, compressed with gzip. Each line is one record with a `company_number` and a `data` object. `data.kind` tells you what sort of record it is.

## The sample

The sample covers about 29,000 companies. For each company in it, the sample keeps all of the company's records. It also includes the companies that own them, so that ownership chains can be followed.

To protect the people in it, we replaced the names, birth dates and addresses of individuals with fake values. A person keeps the same fake details everywhere they appear.

## Licence

Contains public sector information licensed under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
