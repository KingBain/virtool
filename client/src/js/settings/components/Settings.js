/**
 *
 *
 * @copyright 2017 Government of Canada
 * @license MIT
 * @author igboyes
 *
 */

import React from "react";
import { connect } from "react-redux";
import { withRouter, Redirect, Route } from "react-router-dom";
import { Nav, NavItem } from "react-bootstrap";
import { LinkContainer } from "react-router-bootstrap";

import { Flex, FlexItem } from "virtool/js/components/Base";

import SourceTypes from "./General/SourceTypes";
import InternalControl from "./General/InternalControl";
import UniqueNames from "./General/UniqueNames";
import SamplePermissions from "./General/SamplePermissions";
import HTTP from "./Server/HTTP";
import SSL from "./Server/SSL";
import Resources from "./Jobs/Resources";
import Tasks from "./Jobs/Tasks";

const General = () => (
    <div>
        <SourceTypes />
        <InternalControl />
        <UniqueNames />
        <SamplePermissions />
    </div>
);

const Server = () => (
    <div>
        <HTTP />
        <SSL />
    </div>
);

const Jobs = () => (
    <div>
        <Resources />
        <Tasks />
    </div>
);

const Settings = () => {
    return (
        <div className="container">
            <Redirect from="/settings" to="/settings/general"  />

            <Flex>
                <FlexItem>
                    <Nav bsStyle="pills" stacked>
                        <LinkContainer to="/settings/general">
                            <NavItem>General</NavItem>
                        </LinkContainer>

                        <LinkContainer to="/settings/server">
                            <NavItem>Server</NavItem>
                        </LinkContainer>

                        <LinkContainer to="/settings/database">
                            <NavItem>Database</NavItem>
                        </LinkContainer>

                        <LinkContainer to="/settings/jobs">
                            <NavItem>Jobs</NavItem>
                        </LinkContainer>
                    </Nav>
                </FlexItem>

                <FlexItem pad={15}>
                    <div style={{borderRight: "1px solid #e5e5e5", height: "100%"}} />
                </FlexItem>

                <FlexItem pad={15}>
                    <Route path="/settings/general" component={General} />
                    <Route path="/settings/server" component={Server} />
                    <Route path="/settings/jobs" component={Jobs} />
                </FlexItem>
            </Flex>
        </div>
    );
};

Settings.propTypes = {
    source_types: React.PropTypes.object,
    get: React.PropTypes.func
};

const mapStateToProps = (state) => {
    return {
        restrictSourceTypes: state.settings.data.restrict_source_types,
        allowedSourceTypes: state.settings.data.allowed_source_types
    };
};

const mapDispatchToProps = () => {
    return {
        set: (key, value) => {
            console.log(key, value);
        }
    };
};

const SettingsContainer = withRouter(connect(
    mapStateToProps,
    mapDispatchToProps
)(Settings));

export default SettingsContainer;
