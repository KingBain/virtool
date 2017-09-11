/**
 * @license
 * The MIT License (MIT)
 * Copyright 2015 Government of Canada
 *
 * @author
 * Ian Boyes
 *
 * @exports VirusDetail
 */

import React, { PropTypes } from "react";
import { Helmet } from "react-helmet";
import { connect } from "react-redux";
import { Switch, Route, Redirect } from "react-router-dom";
import { LinkContainer } from "react-router-bootstrap";
import { Label, Nav, NavItem } from "react-bootstrap";

import { getVirus, showEditVirus, showRemoveVirus } from "../../actions";
import { Flex, FlexItem, Icon, Spinner } from "virtool/js/components/Base";
import IsolateEditor from "./Editor";
import General from "./General";
import AddIsolate from "./AddIsolate";
import Schema from "./Schema";
import History from "./History";
import EditVirus from "./EditVirus";
import RemoveVirus from "./RemoveVirus";


const VirusSection = (props) => (
    <div>
        <General />
        <IsolateEditor />
        <AddIsolate virusId={props.match.params.virusId} />
    </div>
);

VirusSection.propTypes = {
    match: PropTypes.object
};

class VirusDetail extends React.Component {

    static propTypes = {
        match: PropTypes.object,
        history: PropTypes.object,
        detail: PropTypes.object,
        getVirus: PropTypes.func,
        showEdit: PropTypes.func,
        showRemove: PropTypes.func
    };

    componentDidMount () {
        this.props.getVirus(this.props.match.params.virusId)
    }

    render = () => {

        let content;

        if (this.props.detail) {

            const virusId = this.props.detail.id;

            let modifiedLabel;

            if (this.props.detail.modified) {
                modifiedLabel = (
                    <small>
                        <Label bsStyle="warning" className="with-icon">
                            <Icon name="flag" />
                            Modified
                        </Label>
                    </small>
                );
            }

            const { name, abbreviation } = this.props.detail;

            content = (
                <div>
                    <Helmet>
                        <title>{name}</title>
                    </Helmet>

                    <h3 style={{marginBottom: "20px"}}>
                        <Flex alignItems="flex-end">
                            <FlexItem grow={1}>
                                <Flex alignItems="center">
                                    <strong>
                                        {name}
                                    </strong>
                                    <FlexItem grow={1} pad={5}>
                                        <small className="text-strong">
                                            {abbreviation}
                                        </small>
                                    </FlexItem>
                                </Flex>
                            </FlexItem>

                            {modifiedLabel}

                            <small style={{paddingLeft: "5px"}}>
                                <Icon
                                    bsStyle="warning"
                                    name="pencil"

                                    onClick={() => this.props.showEdit()}
                                />
                            </small>

                            <small style={{paddingLeft: "5px"}}>
                                <Icon
                                    bsStyle="danger"
                                    name="remove"
                                    onClick={() => this.props.showRemove()}
                                />
                            </small>
                        </Flex>
                    </h3>

                    <Nav bsStyle="tabs">
                        <LinkContainer to={`/viruses/${virusId}/virus`}>
                            <NavItem>
                                Virus
                            </NavItem>
                        </LinkContainer>

                        <LinkContainer to={`/viruses/${virusId}/schema`}>
                            <NavItem>
                                Schema
                            </NavItem>
                        </LinkContainer>

                        <LinkContainer to={`/viruses/${virusId}/history`}>
                            <NavItem>
                                History
                            </NavItem>
                        </LinkContainer>
                    </Nav>

                    <EditVirus virusId={virusId} name={name} abbreviation={abbreviation} />
                    <RemoveVirus virusId={virusId} virusName={name} history={this.props.history} />

                    <Switch>
                        <Redirect from="/viruses/:virusId" to={`/viruses/${virusId}/virus`} exact />
                        <Route path="/viruses/:virusId/virus" component={VirusSection} />
                        <Route path="/viruses/:virusId/schema" component={Schema} />
                        <Route path="/viruses/:virusId/history" component={History} />
                    </Switch>
                </div>
            );
        } else {
            content = (
                <div className="text-center">
                    <Spinner />
                </div>
            );
        }

        return (
            <div>
                {content}
            </div>
        );
    };
}

const mapStateToProps = (state) => {
    return {
        detail: state.viruses.detail
    };
};

const mapDispatchToProps = (dispatch) => {
    return {
        getVirus: (virusId) => {
            dispatch(getVirus(virusId));
        },

        showEdit: () => {
            dispatch(showEditVirus());
        },

        showRemove: () => {
            dispatch(showRemoveVirus());
        }
    };
};

const Container = connect(mapStateToProps, mapDispatchToProps)(VirusDetail);

export default Container;