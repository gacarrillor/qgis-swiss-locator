# -*- coding: utf-8 -*-
"""
/***************************************************************************

 QGIS Swiss Locator Plugin
 Copyright (C) 2022 Denis Rouzaud

 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

from PyQt5.QtCore import QUrl
from PyQt5.QtNetwork import QNetworkReply

from qgis.gui import QgisInterface
from qgis.core import QgsApplication, QgsFetchedContent, QgsLocatorResult, QgsLocatorContext, QgsFeedback
from swiss_locator.core.filters.swiss_locator_filter import SwissLocatorFilter, FilterType
from swiss_locator.core.results import WMSLayerResult

import xml.etree.ElementTree as ET


class SwissLocatorFilterWMTS(SwissLocatorFilter):
    def __init__(self, iface: QgisInterface = None, crs: str = None, capabilities = None):
        super().__init__(FilterType.WMTS, iface, crs)

        self.capabilities = capabilities
        self.capabilities_url = f'https://wmts.geo.admin.ch/EPSG/{self.crs}/1.0.0/WMTSCapabilities.xml?lang={self.lang}'

        # do this on main thread only?
        if self.capabilities is None and iface is not None:

            self.content = QgsApplication.networkContentFetcherRegistry().fetch(self.capabilities_url)
            self.content.fetched.connect(self.handle_capabilities_response)

            self.info(self.content.status())

            if self.content.status() == QgsFetchedContent.ContentStatus.Finished:
                file_path = self.content.filePath()
                self.info(f'Swisstopo capabilities already downloaded. Reading from {file_path}')
                self.capabilities = ET.parse(file_path).getroot()
            else:
                self.content.download()

    def clone(self):
        return SwissLocatorFilterWMTS(crs=self.crs, capabilities=self.capabilities)

    def displayName(self):
        return self.tr('Swiss Geoportal WMTS Layers')

    def prefix(self):
        return 'chw'

    def handle_capabilities_response(self):
        self.info(f'Swisstopo capabilities has been downloaded. Reading from {self.content.filePath()}')
        self.capabilities = ET.parse(self.content.filePath()).getroot()

    def fetchResults(self, search: str, context: QgsLocatorContext, feedback: QgsFeedback):
        namespaces = {'wmts': 'http://www.opengis.net/wmts/1.0',
                      'ows': 'http://www.opengis.net/ows/1.1'}

        if len(search) < 2:
            return

        if self.capabilities is None:
            # TODO wait for fetch
            return

        # Search for layers containing the search term in the name or title
        for layer in self.capabilities.findall(f'.//wmts:Layer', namespaces):
            layer_title = layer.find(f'.//ows:Title', namespaces).text
            layer_abstract = layer.find(f'.//ows:Abstract', namespaces).text
            layer_identifier = layer.find(f'.//ows:Identifier', namespaces).text

            results = {}

            if layer_identifier:
                if search in layer_identifier.lower():
                    score = 1
                elif search in layer_title.lower():
                    score = 2
                elif search in layer_abstract.lower():
                    score = 3
                else:
                    continue

                tile_matrix_set = layer.find('.//wmts:TileMatrixSet', namespaces).text
                _format = layer.find('.//wmts:Format', namespaces).text
                style = layer.find('.//wmts:Style/ows:Identifier', namespaces).text

                result = QgsLocatorResult()
                result.filter = self
                result.icon = QgsApplication.getThemeIcon("/mActionAddWmsLayer.svg")

                result.displayString = layer_title
                result.description = layer_abstract
                result.userData = WMSLayerResult(
                    layer=layer_identifier,
                    title=layer_title,
                    url=self.capabilities_url,
                    tile_matrix_set=tile_matrix_set,
                    _format=_format,
                    style=style
                ).as_definition()

                results[result] = score

            # sort the results with score
            results = sorted([result for (result, score) in results.items()])

            for result in results[0:self.settings.value('wmts_limit')]:
                self.resultFetched.emit(result)
                self.result_found = True

