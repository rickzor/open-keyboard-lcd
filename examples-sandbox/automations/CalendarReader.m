#import <Foundation/Foundation.h>
#import <EventKit/EventKit.h>

// Read-only EventKit queries; no calendar data is modified.
int main(int argc, const char *argv[]) {
    @autoreleasepool {
        NSArray<NSString *> *args = NSProcessInfo.processInfo.arguments;
        if ([args containsObject:@"--help"]) {
            puts("calendar-reader [--authorize]: JSON events starting within 120 seconds");
            return 0;
        }
        EKEventStore *store = [EKEventStore new];
        if ([EKEventStore authorizationStatusForEntityType:EKEntityTypeEvent] != EKAuthorizationStatusFullAccess) {
            if (![args containsObject:@"--authorize"]) {
                fputs("Run calendar-reader --authorize interactively first.\n", stderr); return 1;
            }
            __block BOOL done = NO, allowed = NO;
            [store requestFullAccessToEventsWithCompletion:^(BOOL granted, NSError *error) {
                dispatch_async(dispatch_get_main_queue(), ^{ allowed = granted && !error; done = YES; });
            }];
            NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:120];
            while (!done && deadline.timeIntervalSinceNow > 0) {
                [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
            }
            if (!allowed) { fputs("Calendar access unavailable.\n", stderr); return 1; }
        }
        NSDate *now = [NSDate date];
        NSPredicate *predicate = [store predicateForEventsWithStartDate:now
            endDate:[now dateByAddingTimeInterval:120] calendars:nil];
        NSMutableArray *rows = [NSMutableArray new];
        for (EKEvent *event in [store eventsMatchingPredicate:predicate]) {
            if (event.allDay || event.status == EKEventStatusCanceled || [event.startDate compare:now] != NSOrderedDescending) continue;
            BOOL declined = NO;
            for (EKParticipant *person in event.attendees) {
                if (person.currentUser && person.participantStatus == EKParticipantStatusDeclined) declined = YES;
            }
            [rows addObject:@{@"id":event.eventIdentifier ?: event.calendarItemIdentifier,
                @"title":event.title ?: @"Upcoming meeting", @"start":@(event.startDate.timeIntervalSince1970),
                @"all_day":@(event.allDay), @"declined":@(declined)}];
        }
        NSError *error = nil;
        NSData *data = [NSJSONSerialization dataWithJSONObject:rows options:NSJSONWritingSortedKeys error:&error];
        if (!data) { fputs("Calendar serialization failed.\n", stderr); return 1; }
        NSUInteger outputIndex = [args indexOfObject:@"--output"];
        if (outputIndex != NSNotFound && outputIndex + 1 < args.count) {
            NSString *path = args[outputIndex + 1];
            if (![data writeToFile:path options:NSDataWritingAtomic error:&error]) return 1;
            [[NSFileManager defaultManager] setAttributes:@{NSFilePosixPermissions:@0600} ofItemAtPath:path error:nil];
        } else {
            puts([[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding].UTF8String);
        }
        return 0;
    }
}
