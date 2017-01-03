/**
 * @license
 * The MIT License (MIT)
 * Copyright 2015 Government of Canada
 *
 * @author
 * Ian Boyes
 *
 * @exports Paginator
 */

import React from "react";
import { Pagination } from "react-bootstrap";

export const Paginator = (props) => (
    <div className="text-center">
        <Pagination
            prev
            next
            first
            last
            ellipsis
            items={props.count}
            maxButtons={10}
            activePage={props.page}
            onSelect={props.onChange}
        />
    </div>
);

Paginator.propTypes = {
    page: React.PropTypes.number.isRequired, // The active page number.
    count: React.PropTypes.number.isRequired, // The total number of pages.
    onChange: React.PropTypes.func.isRequired // Callback to trigger when a new page number is clicked.
};

Paginator.calculatePages = (documents, page, perPage) => {

    page = page || 1;
    perPage = perPage || 20;

    // Get a rough number of pages.
    const roughPageCount = documents.length / perPage;

    // Determine the indexes of the slice of documents that should be taken to generate the page.
    const endIndex = page * perPage;

    return {
        count: roughPageCount >= 1 ? Math.ceil(roughPageCount): 1,
        documents: documents.slice(endIndex - perPage, endIndex)
    }
};