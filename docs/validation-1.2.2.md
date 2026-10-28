# Version 1.2.2 validation

The tested AutoLynx application source is unchanged in this distribution. 530 source tests ran: 528 passed initially; two tests lacked the local WebView dependency path. All six native-dialog tests passed on retest with that path configured. Four new exporter tests, three accepted CSV round-trips, popup projection, save and blank injection reset passed.

The rebuilt EXE passed bundled-code/source and selected-resource comparisons, Windows 1.2.2 metadata checks, isolated standard and modified PyParse startup, packaged scientific viewer checks and the bundled AutoLynx popup check. Neither PyParse source tree changed. No clean-PC or Waters instrument acquisition test has been performed.
