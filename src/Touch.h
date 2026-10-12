#pragma once
#include "Settings.h"
#include "TouchGesture.h"
void touchService(const Settings& s);
void touchStatus(JsonObject o, const Settings& s);
void touchCalibrate();
TouchGesture::Event touchTake();
