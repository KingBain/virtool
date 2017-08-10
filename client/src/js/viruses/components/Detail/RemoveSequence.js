/**
 * @license
 * The MIT License (MIT)
 * Copyright 2015 Government of Canada
 *
 * @author
 * Ian Boyes
 *
 * @exports RemoveIsolate
 */

import React, { PropTypes } from "react";
import { connect } from "react-redux";
import { Modal } from "react-bootstrap";

import { removeSequence, hideVirusModal } from "../../actions";
import { Button } from "virtool/js/components/Base";

const RemoveSequence = (props) => (
    <Modal show={Boolean(props.sequenceId)} onHide={props.onHide} dialogClassName="modal-danger">
        <Modal.Header onHide={props.onHide} closeButton>
            Remove Sequence
        </Modal.Header>
        <Modal.Body>
            Are you sure you want to remove the sequence <strong>{props.sequenceId}</strong> from
            <strong> {props.isolateName}</strong>?
        </Modal.Body>
        <Modal.Footer>
            <Button
                bsStyle="danger"
                icon="checkmark"
                onClick={() => props.onConfirm(props.virusId, props.isolateId, props.sequenceId, props.onSuccess)}
            >
                Confirm
            </Button>
        </Modal.Footer>
    </Modal>
);

RemoveSequence.propTypes = {
    virusId: PropTypes.string,
    isolateId: PropTypes.string,
    isolateName: PropTypes.string,
    sequenceId: PropTypes.oneOfType([PropTypes.bool, PropTypes.string]),
    onHide: PropTypes.func,
    onConfirm: PropTypes.func,
    onSuccess: PropTypes.func
};

const mapStateToProps = (state) => {
    return {
        sequenceId: state.viruses.removeSequence
    };
};

const mapDispatchToProps = (dispatch) => {
    return {
        onHide: () => {
            dispatch(hideVirusModal());
        },

        onConfirm: (virusId, isolateId, onSuccess) => {
            dispatch(removeSequence(virusId, isolateId, onSuccess));
        }
    };
};

const Container = connect(mapStateToProps, mapDispatchToProps)(RemoveSequence);

export default Container;
