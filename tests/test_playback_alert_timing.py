"""Alert occurrence UTC must use real time, even though replay runs at 2x."""
from datetime import datetime, timedelta
from unittest.mock import patch
from app.services import monitoring_alerts

NOW=datetime(2026,11,20,12)


class Cursor:
    def __init__(self,occurrences,recorded=()):
        self.occurrences=occurrences
        self.recorded=recorded
        self.sql=''
        self.inserts=[]

    def execute(self,sql,params=()):
        self.sql=sql
        if 'INSERT INTO monitoring_alert_events' in sql:
            self.inserts.append(params)

    def fetchone(self):
        return dict(total_ms=30000)

    def fetchall(self):
        if 'SELECT cycle_number' in self.sql:
            return self.recorded
        return [dict(start_ms=offset,set_number=4,position=i,measurement_id=i+1,
                     prediction_id=None,image_name=f'{i}.png',sensor_name=f'{i}.csv',
                     original_wear_um=200,predicted_wear_um=None,original_type='flank_wear',
                     predicted_type=None) for i,offset in enumerate(self.occurrences)]


def state(elapsed=0,seconds_ago=12.5):
    return dict(status='running',session_id='session',elapsed_ms=elapsed,
                resumed_at=NOW-timedelta(seconds=seconds_ago))


def test_delayed_worker_records_real_occurrence_time_at_two_times():
    cursor=Cursor([0,10000])
    monitoring_alerts.emit_due_alerts(cursor,state(),NOW)
    assert len(cursor.inserts)==2
    assert cursor.inserts[0][-2]==NOW-timedelta(seconds=12.5)
    assert cursor.inserts[1][-2]==NOW-timedelta(seconds=7.5)
    assert all(row[-1]==NOW for row in cursor.inserts)


def test_next_cycle_occurs_after_fifteen_real_seconds():
    cursor=Cursor([0])
    monitoring_alerts.emit_due_alerts(cursor,state(seconds_ago=15),NOW)
    assert [row[1] for row in cursor.inserts]==[1,2]
    assert cursor.inserts[1][-2]-cursor.inserts[0][-2]==timedelta(seconds=15)


def test_resume_keeps_previously_accumulated_source_milliseconds():
    cursor=Cursor([0])
    monitoring_alerts.emit_due_alerts(cursor,state(elapsed=71000,seconds_ago=9.5),NOW)
    current=[row for row in cursor.inserts if row[1]==4]
    assert len(current)==1
    assert current[0][-2]==NOW


def test_recorded_occurrence_is_not_duplicated():
    cursor=Cursor([0],recorded=[dict(cycle_number=1,set_number=4,position=0)])
    monitoring_alerts.emit_due_alerts(cursor,state(seconds_ago=15),NOW)
    assert len(cursor.inserts)==1
    assert cursor.inserts[0][1]==2


def test_paused_state_does_not_emit_events():
    cursor=Cursor([0])
    monitoring_alerts.emit_due_alerts(cursor,{**state(),'status':'paused'},NOW)
    assert cursor.inserts==[]
