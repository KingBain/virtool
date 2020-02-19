import React from "react";
import { connect } from "react-redux";
import SampleRights from "../../administration/components/SampleRights";
import UniqueNames from "../../administration/components/UniqueNames";
import { mapSettingsStateToProps } from "../../administration/mappers";
import { LoadingPlaceholder, ViewHeader } from "../../base";

export const SamplesSettings = ({ loading }) => {
    if (loading) {
        return <LoadingPlaceholder />;
    }

    return (
        <div className="settings-container">
            <ViewHeader title="Sample Settings" />
            <UniqueNames />
            <SampleRights />
        </div>
    );
};

export default connect(mapSettingsStateToProps)(SamplesSettings);